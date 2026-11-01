"""Real host filesystem fixtures and permission inspection, with no POSIX emulation."""
import os
import stat
from functools import lru_cache
from pathlib import Path


def deployed_environment(**extra):
    result={'PATH':os.path.join(os.environ.get('SystemRoot','C:/Windows'),'System32') if os.name=='nt' else '/usr/bin:/bin','NEX_RESOURCE_DIR':'/absent'}
    if os.name=='nt':
        for key in ('SystemRoot','WINDIR','SystemDrive','TEMP','TMP','USERPROFILE','LOCALAPPDATA'):
            if key in os.environ:result[key]=os.environ[key]
    result.update(extra)
    return result


def shared_read(path):
    """Keep a physical file open while permitting an atomic Windows replacement."""
    if os.name!='nt':return open(path,'rb')
    import ctypes as C
    from ctypes import wintypes as W
    import msvcrt
    kernel=C.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE]
    kernel.CreateFileW.restype=W.HANDLE;kernel.CloseHandle.argtypes=[W.HANDLE]
    handle=kernel.CreateFileW(os.fspath(path),0x80000000,7,None,3,0x80,None)
    if handle==C.c_void_p(-1).value:raise C.WinError(C.get_last_error())
    try:fd=msvcrt.open_osfhandle(handle,os.O_RDONLY|os.O_BINARY)
    except BaseException:kernel.CloseHandle(handle);raise
    return os.fdopen(fd,'rb')


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
    embedded='import sys;sys.argv[0]=sys.argv.pop(1);exec(compile('+repr(source)+',sys.argv[0],"exec"))'
    launcher.write_text('#include "host_test.h"\nint wmain(int argc,wchar_t **argv){'
        'wchar_t module[32768];auto size=GetModuleFileNameW(nullptr,module,32768);if(!size||size>=32768)return 124;'
        'std::vector<std::string> args={"-c",'+json.dumps(embedded,ensure_ascii=False)+',nexrt::platform::utf8(std::wstring(module,size))};'
        'for(int i=1;i<argc;++i)args.push_back(nexrt::platform::utf8(argv[i]));'
        'return int(nex_test::run(std::filesystem::path(nexrt::platform::wide('
        +json.dumps(sys.executable)+')),args,true,true));}\n',encoding='utf-8',newline='\n')
    command=[str(compiler),'-std=c++20','-O2','-static','-municode','-I'+str(repo/'tests'),
             '-I'+str(repo/'runtime'),str(launcher),'-o',str(path)]
    result=run_native(command,capture_output=True,text=True,timeout=120)
    if result.returncode:raise RuntimeError(result.stdout+result.stderr)
    # Build-tool probes derive their matching RC tools beside the driver.
    for name in ('llvm-rc.exe','llvm-cvtres.exe'):
        target=Path(compiler).parent/name;alias=path.parent/name
        if target.is_file() and not alias.exists():alias.symlink_to(target)
    return path


def temporary_environment(directory):
    value=str(directory)
    return {name:value for name in ('TEMP','TMP','TMPDIR','TEMPDIR')}


def exit_code(value):
    return int(value or 0)&(0xffffffff if os.name=='nt' else 0xff)


def sparse_file(stream):
    if os.name!='nt':return
    import ctypes as C
    from ctypes import wintypes as W
    import msvcrt
    kernel=C.WinDLL('kernel32',use_last_error=True)
    kernel.DeviceIoControl.argtypes=[W.HANDLE,W.DWORD,C.c_void_p,W.DWORD,C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.c_void_p]
    kernel.DeviceIoControl.restype=W.BOOL
    count=W.DWORD()
    if not kernel.DeviceIoControl(msvcrt.get_osfhandle(stream.fileno()),0x900c4,None,0,None,0,C.byref(count),None):raise C.WinError(C.get_last_error())


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



def copy_link_image(source, destination):
    """Copy a genuine DLL and the import archive needed by later fixture links."""
    import shutil
    source=Path(source);destination=Path(destination)
    result=shutil.copyfile(source,destination)
    if os.name=='nt' and source.suffix.lower()=='.dll' and Path(str(source)+'.a').is_file():
        shutil.copyfile(str(source)+'.a',str(destination)+'.a')
    return result

def run_native(arguments, *args, **kwargs):
    """Compile the same native fixture with the Windows SDK's real link closure."""
    import subprocess
    command=list(map(str,arguments));rename=None;link_stage=None;link_capture=None
    if os.name=='nt':
        program=Path(command[0])
        if program.parent!=Path('.') and not program.is_file() and program.with_name(program.name+'.exe').is_file():
            command[0]=str(program.with_name(program.name+'.exe'))
        if Path(command[0]).name.lower() in ('openssl','openssl.exe') and 'req' in command and all(flag in command for flag in ('-out','-keyout')):
            outputs=[command[command.index(flag)+1] for flag in ('-out','-keyout')]
            if any(not value.isascii() for value in outputs):
                import shutil
                import tempfile
                with tempfile.TemporaryDirectory(prefix='nex-tls-fixture-') as directory:
                    if not directory.isascii():raise ValueError('the selected OpenSSL CLI requires an ASCII staging directory')
                    copies=[]
                    for flag in ('-out','-keyout'):
                        index=command.index(flag)+1;destination=Path(command[index])
                        if not destination.is_absolute():destination=Path(kwargs.get('cwd',Path.cwd()))/destination
                        staged=Path(directory)/(flag[1:]+'.pem');copies.append((staged,destination));command[index]=str(staged)
                    result=subprocess.run(command,*args,**kwargs)
                    if result.returncode==0:
                        for source,destination in copies:shutil.copy2(source,destination)
                    return result
    compiling=any(value in command for value in ('-shared','-c','-emit-llvm')) or any(value.startswith('-std=') for value in command) or ('-o' in command and any(value.lower().endswith(('.o','.obj','.a','.ll','.c','.cpp')) for value in command[1:]))
    if os.name=='nt' and compiling:
        command=[value.replace('--build-id=sha1','--build-id') for value in command if value!='-ldl' and not value.startswith(('-Wl,-soname,','-Wl,-rpath,','-Wl,-z,'))]
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
            output_index=command.index('-o')+1;requested=Path(command[output_index])
            if not str(requested).isascii() or '%' in str(requested):
                import tempfile
                import shutil
                directory=Path(tempfile.gettempdir())
                while '%' in str(directory) or not str(directory).isascii():directory=directory.parent
                link_stage=tempfile.TemporaryDirectory(prefix='nex-fixture-link-',dir=directory)
                staged=Path(link_stage.name)/requested.name
                command[output_index]=str(staged);link_capture=(staged,requested)
            command=[str(Path(value).with_name(Path(value).name+'.a'))
                     if index!=output_index and value.lower().endswith('.dll') and Path(value+'.a').is_file() else value for index,value in enumerate(command)]
            search=[]
            for index,value in enumerate(command):
                if value=='-L' and index+1<len(command):search.append(Path(command[index+1]))
                elif value.startswith('-L') and len(value)>2:search.append(Path(value[2:]))
            for index,value in enumerate(command):
                if not value.startswith('-l') or len(value)<=2:continue
                for directory in search:
                    if (directory/('lib'+value[2:]+'.a')).is_file():break
                    archive=directory/('lib'+value[2:]+'.dll.a')
                    if archive.is_file():command[index]=str(archive);break
            for value in ('-static','-Wl,--stack,8388608','-lntdll','-lbcrypt','-ladvapi32',
                          '-lcrypt32','-lws2_32','-lsecur32','-ldbghelp','-ldwmapi'):
                if value not in command:command.append(value)
            if host_exports and '-shared' not in command:
                output=Path(command[command.index('-o')+1])
                command+=['-Wl,--export-all-symbols','-Xlinker','--out-implib','-Xlinker',
                          str(output.parent/('lib'+output.stem+'.dll.a'))]
            if '-shared' in command:
                if '-Wl,--exclude-symbols,CRYPTO_memcmp' not in command:command.append('-Wl,--exclude-symbols,CRYPTO_memcmp')
                if any(value.endswith('entry.def') for value in command):command.append('-Wl,--export-all-symbols')
                index=command.index('-o')+1;output=Path(command[index])
                command+=['-Xlinker','--out-implib','-Xlinker',str(output)+'.a']
                if not output.suffix:
                    rename=(output.with_name(output.name+'.dll'),output)
                    command[index]=str(rename[0])
            else:command.extend(['-x','none',windows_fixture_resource(command[0])])
        if isinstance(arguments,list):arguments[:]=command
    result=subprocess.run(command,*args,**kwargs)
    if rename and result.returncode==0:rename[0].replace(rename[1])
    if link_capture and result.returncode==0:
        source,destination=link_capture
        if not source.is_file() and source.with_name(source.name+'.exe').is_file():source=source.with_name(source.name+'.exe')
        shutil.copy2(source,destination)
        if Path(str(source)+'.a').is_file():shutil.copy2(str(source)+'.a',str(destination)+'.a')
    if link_stage:link_stage.cleanup()
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


def native_task_definitions(listing, image, compiler):
    """Count physical code definitions, excluding PE import jump thunks."""
    import platform
    import re
    import subprocess
    names=re.findall(r'^([^ ]+__task_step) ',listing,re.M)
    if os.name=='nt':
        tool=Path(compiler).parent/'llvm-readobj.exe'
        result=subprocess.run([str(tool),'--coff-imports',str(image)],capture_output=True,text=True,timeout=60)
        if result.returncode:raise RuntimeError(result.stdout+result.stderr)
        imports=set(re.findall(r'^\s*Symbol: (\S+) \(\d+\)\s*$',result.stdout,re.M))
        return [name for name in names if name not in imports]
    return [name[1:] if name.startswith('_') else name for name in names] if platform.system()=='Darwin' else names


def needed_windows_dlls(archives, compiler):
    """Retain each real import descriptor without whole-archiving null sentinels."""
    import re
    import subprocess
    result=[]
    for archive in archives:
        read=subprocess.run([str(Path(compiler).parent/'llvm-nm.exe'),'--defined-only','--format=posix',str(archive)],capture_output=True,text=True,timeout=60)
        if read.returncode:raise RuntimeError(read.stdout+read.stderr)
        names=sorted(re.findall(r'^(__imp_\S+) [A-Z] ',read.stdout,re.M))
        if not names:raise ValueError('expected real imports in the DLL archive: '+str(archive))
        names=sorted(names,key=lambda name:('__task_code_address' not in name,name))
        result+=['-Xlinker','--undefined='+names[0],str(archive)]
    return result


def shared_profile_objects(objects, flags, compiler, runtime, run):
    """Use the production PE host-identity bridge only in the shared runtime."""
    if os.name!='nt':return objects
    import hashlib
    import json
    result=[]
    for obj in objects:
        if obj.name!='nex_profile.cpp.o':result.append(obj);continue
        target=obj.with_name('nex_profile.windows-shared.cpp.o')
        options=[*flags,'-DNEX_SHARED_WINDOWS_RUNTIME']
        if '-DNEX_SHARED_PROFILE_RUNTIME' not in options:options.append('-DNEX_SHARED_PROFILE_RUNTIME')
        recipe={'compiler':hashlib.sha256(Path(compiler).read_bytes()).hexdigest(),
                'source':hashlib.sha256((runtime/'nex_profile.cpp').read_bytes()).hexdigest(),
                'flags':options,'headers':{str(p.relative_to(runtime)):hashlib.sha256(p.read_bytes()).hexdigest() for p in runtime.rglob('*') if p.is_file() and p.suffix in ('.h','.hpp')}}
        stamp=target.with_suffix('.recipe.json')
        if not target.is_file() or not stamp.is_file() or json.loads(stamp.read_bytes())!=recipe:
            run('compile-shared-profile-identity',[compiler,*options,'-c',runtime/'nex_profile.cpp','-o',target])
            stamp.write_text(json.dumps(recipe,sort_keys=True),encoding='utf-8')
        result.append(target)
    return result


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


def windows_workload_descendant(root, compiler, environment, finite=False):
    'Create a genuine native heartbeat child inside the supervisor Job.'
    import subprocess
    root=Path(root);source=root/'workload-descendant.c';image=root/'workload-descendant.exe'
    source.write_text(r'''#include <windows.h>
int main(void){wchar_t path[32768];if(!GetEnvironmentVariableW(L"NEX_SOURCE_FFI_MARKER",path,32768))return 2;
for(;;){HANDLE file=CreateFileW(path,FILE_APPEND_DATA,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,0,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,0);if(file==INVALID_HANDLE_VALUE)return 3;DWORD size=0;char event='H';if(!WriteFile(file,&event,1,&size,0)||size!=1)return 4;CloseHandle(file);Sleep(20);}}
''',encoding='utf-8',newline='\n')
    result=run_native([compiler,'-x','c','-std=c11',source,'-o',image],capture_output=True,text=True,timeout=120)
    if result.returncode:raise RuntimeError(result.stdout+result.stderr)
    environment['NEX_WORKLOAD_CHILD_EXE']=str(image)
    code=r'''mark('C');BOOL in_job=FALSE;if(!IsProcessInJob(GetCurrentProcess(),0,&in_job)||!in_job)return NEX_FFI_INTERNAL;
wchar_t child_path[32768],file_path[32768],pending[32768];if(!GetEnvironmentVariableW(L"NEX_WORKLOAD_CHILD_EXE",child_path,32768)||!GetEnvironmentVariableW(L"NEX_WORKLOAD_CHILDREN",file_path,32768))return NEX_FFI_ARGUMENT;
if(GetFileAttributesW(file_path)==INVALID_FILE_ATTRIBUTES){if(wcslen(file_path)>32700)return NEX_FFI_ARGUMENT;wcscpy(pending,file_path);wcscat(pending,L".pending");HANDLE file=CreateFileW(pending,GENERIC_WRITE,0,0,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,0);if(file==INVALID_HANDLE_VALUE)return NEX_FFI_INTERNAL;
STARTUPINFOW startup={0};startup.cb=sizeof(startup);PROCESS_INFORMATION process={0};if(!CreateProcessW(child_path,0,0,0,FALSE,CREATE_NO_WINDOW,0,0,&startup,&process)){CloseHandle(file);return NEX_FFI_INTERNAL;}DWORD child=process.dwProcessId;CloseHandle(process.hThread);CloseHandle(process.hProcess);
DWORD parent=0;HANDLE snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);PROCESSENTRY32W row={0};row.dwSize=sizeof(row);if(snapshot!=INVALID_HANDLE_VALUE){if(Process32FirstW(snapshot,&row))do{if(row.th32ProcessID==GetCurrentProcessId()){parent=row.th32ParentProcessID;break;}}while(Process32NextW(snapshot,&row));CloseHandle(snapshot);}if(!parent){CloseHandle(file);return NEX_FFI_INTERNAL;}
char line[128];int count=snprintf(line,sizeof(line),"%lu %lu %lu\n",(unsigned long)GetCurrentProcessId(),(unsigned long)parent,(unsigned long)child);DWORD size=0;BOOL written=WriteFile(file,line,(DWORD)count,&size,0);CloseHandle(file);if(!written||size!=(DWORD)count||!MoveFileExW(pending,file_path,MOVEFILE_WRITE_THROUGH))return NEX_FFI_INTERNAL;}
'''
    return code+(r'if(getenv("NEX_WORKLOAD_INTERRUPT")){for(;;)Sleep(1000);}Sleep(250);' if finite else 'for(;;)Sleep(1000);')


def windows_live_descendants(record, terminate=False):
    import ctypes as C
    from ctypes import wintypes as W
    kernel=C.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];kernel.OpenProcess.restype=W.HANDLE
    kernel.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD];kernel.WaitForSingleObject.restype=W.DWORD
    kernel.TerminateProcess.argtypes=[W.HANDLE,W.UINT];kernel.TerminateProcess.restype=W.BOOL
    kernel.CloseHandle.argtypes=[W.HANDLE]
    values=list(map(int,Path(record).read_text().split()));live=[]
    if len(values)!=3:raise ValueError('invalid fixture process record')
    for pid in (values[0],values[2]):
        handle=kernel.OpenProcess(0x100000|(1 if terminate else 0),False,pid)
        if not handle:
            if C.get_last_error()==87:continue
            raise C.WinError(C.get_last_error())
        try:
            if kernel.WaitForSingleObject(handle,0)==0x102:
                live.append(pid)
                if terminate:
                    if not kernel.TerminateProcess(handle,137):raise C.WinError(C.get_last_error())
                    kernel.WaitForSingleObject(handle,2000)
        finally:kernel.CloseHandle(handle)
    return live
