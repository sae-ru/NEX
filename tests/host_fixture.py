"""Real host filesystem fixtures and permission inspection, with no POSIX emulation."""
import os
import stat
from functools import lru_cache
from pathlib import Path


def python_executable(path, source, compiler):
    """Run the same Python fixture through a real executable on Windows."""
    if os.name != 'nt':
        path.write_text(source, encoding='utf-8', newline='\n')
        path.chmod(0o700)
        return path
    import json
    import subprocess
    import sys
    import ast
    # MSVCRT execv joins arguments without the quoting subprocess provides.
    # Keep literal Unicode/space paths and the real compiler's return status.
    tree=ast.parse(source);lines=source.splitlines(True);offsets=[0]
    for line in lines:offsets.append(offsets[-1]+len(line))
    def position(line,column):
        return offsets[line-1]+len(lines[line-1].encode('utf-8')[:column].decode('utf-8'))
    replacements=[]
    for node in ast.walk(tree):
        if (isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and
                isinstance(node.func.value,ast.Name) and node.func.value.id=='os' and
                node.func.attr=='execv' and len(node.args)==2):
            arguments=ast.get_source_segment(source,node.args[1])
            replacements.append((position(node.lineno,node.col_offset),
                position(node.end_lineno,node.end_col_offset),
                '__import__("sys").exit(__import__("subprocess").call('+arguments+'))'))
    for start,end,value in sorted(replacements,reverse=True):source=source[:start]+value+source[end:]
    path=Path(path).with_suffix('.exe')
    script=path.with_suffix('.py');script.write_text(source,encoding='utf-8',newline='\n')
    repo=Path(__file__).resolve().parents[1]
    launcher=path.with_suffix('.cpp')
    launcher.write_text('#include "host_test.h"\nint wmain(int argc,wchar_t **argv){'
        'std::vector<std::string> args={"-c",'+json.dumps(source,ensure_ascii=False)+'};'
        'for(int i=1;i<argc;++i)args.push_back(nexrt::platform::utf8(argv[i]));'
        'return int(nex_test::run(std::filesystem::path(nexrt::platform::wide('
        +json.dumps(sys.executable)+')),args,true,true));}\n',encoding='utf-8',newline='\n')
    command=[str(compiler),'-std=c++20','-O2','-static','-municode','-I'+str(repo/'tests'),
             '-I'+str(repo/'runtime'),str(launcher),'-o',str(path)]
    result=subprocess.run(command,capture_output=True,text=True,timeout=120)
    if result.returncode:raise RuntimeError(result.stdout+result.stderr)
    # Build-tool probes derive their matching RC tools beside the driver.
    for name in ('llvm-rc.exe','llvm-cvtres.exe'):
        target=Path(compiler).parent/name;alias=path.parent/name
        if target.is_file() and not alias.exists():alias.symlink_to(target)
    return path


def exit_code(value):
    return int(value or 0)&(0xffffffff if os.name=='nt' else 0xff)


def control_event(process, kind):
    """Request cooperative native Windows shutdown; never force a passing exit."""
    import ctypes as C
    from ctypes import wintypes as W
    kernel=C.WinDLL('kernel32',use_last_error=True)
    kernel.OpenEventW.argtypes=[W.DWORD,W.BOOL,W.LPCWSTR];kernel.OpenEventW.restype=W.HANDLE
    kernel.SetEvent.argtypes=[W.HANDLE];kernel.SetEvent.restype=W.BOOL
    kernel.CloseHandle.argtypes=[W.HANDLE];kernel.CloseHandle.restype=W.BOOL
    event=kernel.OpenEventW(2,False,'Local\\NEX.'+kind+'.Stop.'+str(process.pid))
    if not event:raise C.WinError(C.get_last_error())
    try:
        if not kernel.SetEvent(event):raise C.WinError(C.get_last_error())
    finally:kernel.CloseHandle(event)


def stop_server(process):
    import signal
    if os.name=='nt':control_event(process,'Server')
    else:process.send_signal(signal.SIGTERM)


def interrupt_task(process):
    import signal
    if os.name=='nt':control_event(process,'Task')
    else:process.send_signal(signal.SIGINT)


def run_native(arguments, *args, **kwargs):
    """Compile the same native fixture with the Windows SDK's real link closure."""
    import subprocess
    command=list(map(str,arguments));rename=None
    if os.name=='nt':
        program=Path(command[0])
        if program.parent!=Path('.') and not program.is_file() and program.with_name(program.name+'.exe').is_file():
            command[0]=str(program.with_name(program.name+'.exe'))
    compiling=any(value in command for value in ('-shared','-c','-emit-llvm')) or any(value.startswith('-std=') for value in command)
    if os.name=='nt' and compiling:
        command=[value.replace('--build-id=sha1','--build-id') for value in command if value!='-ldl']
        host_exports='-Wl,--export-dynamic' in command
        command=[value for value in command if value!='-Wl,--export-dynamic']
        for value in ('--export-dynamic','-export_dynamic'):
            while value in command:
                index=command.index(value)
                if not index or command[index-1]!='-Xlinker':raise ValueError('unexpected export fixture option shape')
                del command[index-1:index+1];host_exports=True
        for option in ('-soname','-rpath'):
            while option in command:
                index=command.index(option)
                if index and command[index-1]=='-Xlinker':
                    count=4 if index+1<len(command) and command[index+1]=='-Xlinker' else 3
                    del command[index-1:index-1+count]
                else:raise ValueError('unexpected ELF-only fixture option shape')
        command+=['-I'+str(Path(__file__).resolve().parent)]
        linking='-o' in command and not any(value in command for value in ('-c','-E','-S'))
        if linking:
            command=[str(Path(value).with_name(Path(value).name+'.a'))
                     if value.lower().endswith('.dll') and Path(value+'.a').is_file() else value for value in command]
            for value in ('-static','-Wl,--stack,8388608','-lntdll','-lbcrypt','-ladvapi32',
                          '-lcrypt32','-lws2_32','-lsecur32','-ldbghelp','-ldwmapi'):
                if value not in command:command.append(value)
            if host_exports and '-shared' not in command:
                output=Path(command[command.index('-o')+1])
                command+=['-Wl,--export-all-symbols','-Xlinker','--out-implib','-Xlinker',
                          str(output.parent/('lib'+output.stem+'.dll.a'))]
            if '-shared' in command:
                index=command.index('-o')+1;output=Path(command[index])
                command+=['-Xlinker','--out-implib','-Xlinker',str(output)+'.a']
                if not output.suffix:
                    rename=(output.with_name(output.name+'.dll'),output)
                    command[index]=str(rename[0])
            else:command.append(windows_fixture_resource(command[0]))
        if isinstance(arguments,list):arguments[:]=command
    result=subprocess.run(command,*args,**kwargs)
    if rename and result.returncode==0:rename[0].replace(rename[1])
    return result


@lru_cache(maxsize=8)
def windows_fixture_resource(compiler):
    import atexit
    import json
    import platform
    import subprocess
    import tempfile
    temporary=Path(tempfile.gettempdir())
    while '%' in str(temporary):temporary=temporary.parent
    stage=tempfile.TemporaryDirectory(prefix='nex-fixture-resource-',dir=temporary)
    atexit.register(stage.cleanup)
    root=Path(stage.name);binary=Path(compiler).resolve().parent
    manifest=Path(__file__).resolve().parents[1]/'runtime/nex_windows.manifest'
    rc=root/'fixture.rc';rc.write_text('1 24 '+json.dumps(manifest.as_posix(),ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
    res=root/'fixture.res';obj=root/'fixture.o'
    for command in ([str(binary/'llvm-rc.exe'),'/no-preprocess','/X','/C','65001','/FO',str(res),str(rc)],
                    [str(binary/'llvm-cvtres.exe'),'/MACHINE:'+('ARM64' if platform.machine().lower() in ('arm64','aarch64') else 'X64'),'/TIMESTAMP:0','/OUT:'+str(obj),str(res)]):
        result=subprocess.run(command,capture_output=True,text=True,timeout=60)
        if result.returncode:raise RuntimeError(result.stdout+result.stderr)
    # Keep the directory owner alive until this test process exits.
    windows_fixture_resource.owners.append(stage)
    return str(obj)


windows_fixture_resource.owners=[]


def host_cpp(source):
    if os.name=='nt':
        header=(Path(__file__).resolve().parent/'host_dlfcn.h').as_posix()
        source=source.replace('#include <dlfcn.h>','#include "'+header+'"')
    return source


def probe_dll_inputs(probe, directory):
    """Expose the private test entry and import its exact host runtime on PE."""
    path=Path(directory)/'entry.def'
    path.write_bytes(b'EXPORTS\nmain\n')
    probe=Path(probe)
    return [str(path),str(probe.parent/('lib'+probe.stem+'.dll.a'))]


def nonregular(path, mode=0o600):
    if os.name != 'nt':
        os.mkfifo(path, mode)
        return
    import ctypes as C
    from ctypes import wintypes as W
    sockets=C.WinDLL('ws2_32',use_last_error=True)
    sockets.WSAStartup.argtypes=[W.WORD,C.c_void_p];sockets.WSAStartup.restype=C.c_int
    sockets.socket.argtypes=[C.c_int,C.c_int,C.c_int];sockets.socket.restype=C.c_size_t
    sockets.bind.argtypes=[C.c_size_t,C.c_void_p,C.c_int];sockets.bind.restype=C.c_int
    sockets.closesocket.argtypes=[C.c_size_t];sockets.closesocket.restype=C.c_int
    sockets.WSAGetLastError.restype=C.c_int
    class Address(C.Structure):_fields_=[('family',C.c_ushort),('path',C.c_char*108)]
    data=C.create_string_buffer(512)
    if sockets.WSAStartup(0x202,data):raise OSError('native Winsock startup failed')
    handle=C.c_size_t(-1).value
    try:
        raw=os.fsencode(os.path.abspath(path))
        if len(raw)>=108:raise ValueError('native AF_UNIX fixture path exceeds108 bytes')
        address=Address(1,raw);handle=sockets.socket(1,1,0)
        if handle==C.c_size_t(-1).value:raise OSError(sockets.WSAGetLastError(),'native AF_UNIX socket failed')
        # bind creates a genuine NTFS AF_UNIX reparse point. Closing the
        # socket leaves its nonregular filesystem name for the rejection test.
        if sockets.bind(handle,C.byref(address),C.sizeof(address)):
            raise OSError(sockets.WSAGetLastError(),'native AF_UNIX bind failed')
    finally:
        if handle!=C.c_size_t(-1).value:sockets.closesocket(handle)
        sockets.WSACleanup()


def private_permissions(path, mode):
    if os.name != 'nt':return stat.S_IMODE(os.stat(path).st_mode)==mode
    import ctypes as C
    from ctypes import wintypes as W
    kernel=C.WinDLL('kernel32',use_last_error=True);security=C.WinDLL('advapi32',use_last_error=True)
    kernel.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE];kernel.CreateFileW.restype=W.HANDLE
    kernel.CloseHandle.argtypes=[W.HANDLE];kernel.CloseHandle.restype=W.BOOL
    kernel.GetCurrentProcess.restype=W.HANDLE
    kernel.LocalFree.argtypes=[C.c_void_p];kernel.LocalFree.restype=C.c_void_p
    security.OpenProcessToken.argtypes=[W.HANDLE,W.DWORD,C.POINTER(W.HANDLE)];security.OpenProcessToken.restype=W.BOOL
    security.GetTokenInformation.argtypes=[W.HANDLE,C.c_int,C.c_void_p,W.DWORD,C.POINTER(W.DWORD)];security.GetTokenInformation.restype=W.BOOL
    security.GetSecurityInfo.argtypes=[W.HANDLE,C.c_int,W.DWORD,C.POINTER(C.c_void_p),C.c_void_p,C.POINTER(C.c_void_p),C.c_void_p,C.POINTER(C.c_void_p)];security.GetSecurityInfo.restype=W.DWORD
    security.GetAce.argtypes=[C.c_void_p,W.DWORD,C.POINTER(C.c_void_p)];security.GetAce.restype=W.BOOL
    security.EqualSid.argtypes=[C.c_void_p,C.c_void_p];security.EqualSid.restype=W.BOOL
    security.GetSecurityDescriptorControl.argtypes=[C.c_void_p,C.POINTER(W.WORD),C.POINTER(W.DWORD)];security.GetSecurityDescriptorControl.restype=W.BOOL
    file=kernel.CreateFileW(os.fspath(path),0x20000,7,None,3,0x02200000,None)
    if file==C.c_void_p(-1).value:raise C.WinError(C.get_last_error())
    descriptor=C.c_void_p();token=W.HANDLE()
    try:
        owner=C.c_void_p();acl=C.c_void_p()
        status=security.GetSecurityInfo(file,1,5,C.byref(owner),None,C.byref(acl),None,C.byref(descriptor))
        if status:raise C.WinError(status)
        if not security.OpenProcessToken(kernel.GetCurrentProcess(),8,C.byref(token)):raise C.WinError(C.get_last_error())
        size=W.DWORD();security.GetTokenInformation(token,1,None,0,C.byref(size));data=C.create_string_buffer(size.value)
        if not security.GetTokenInformation(token,1,data,size,C.byref(size)):raise C.WinError(C.get_last_error())
        sid=C.c_void_p.from_buffer(data).value
        if not owner or not acl or not security.EqualSid(owner,sid):return False
        count=C.c_ushort.from_address(acl.value+4).value
        if not count:return False
        granted=0
        for index in range(count):
            raw=C.c_void_p()
            if not security.GetAce(acl,index,C.byref(raw)):raise C.WinError(C.get_last_error())
            if C.c_ubyte.from_address(raw.value).value!=0 or not security.EqualSid(raw.value+8,sid):return False
            granted|=C.c_uint32.from_address(raw.value+4).value
        minimum=0x23 if mode==0o700 else 3
        return granted&minimum==minimum
    finally:
        if descriptor:kernel.LocalFree(descriptor)
        if token:kernel.CloseHandle(token)
        kernel.CloseHandle(file)
