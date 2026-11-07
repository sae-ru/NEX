"""Owned ephemeral AppContainer profiles for native Windows SDK qualification.

Call from a standard-user broker, using a separately built and calibrated
job_observer. No original-source ACL or network-policy changes are performed.
"""
from pathlib import Path
import ctypes as C
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid

from job_observer import observe


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb')as source:
        for block in iter(lambda:source.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


class Profile:
    """Create a fresh per-app profile; never open/reuse an existing profile."""
    def __init__(self, *, name=None, capabilities=()):
        if os.name!='nt':raise RuntimeError('AppContainer requires native Windows')
        from ctypes import wintypes as W
        self.W=W;self.name=name or 'NEX.SDK.'+uuid.uuid4().hex
        if not re.fullmatch(r'[-_. A-Za-z0-9]{1,64}',self.name):
            raise ValueError('invalid AppContainer profile name')
        self.capabilities=list(capabilities)
        if len(self.capabilities)>64 or any(not isinstance(sid,str)or
                len(sid)>184 or not re.fullmatch(r'S-1-15-3-(?:[0-9]+-)*[0-9]+',sid)
                for sid in self.capabilities):
            raise ValueError('capabilities must be explicit AppPackage capability SIDs')
        self.created=False;self.deleted=False;self.safe_to_cleanup=True
        self.owner_thread=threading.get_ident()
        self.path=None;self.sid=None;self.runs=[];self.copies=[]
        self.k=C.WinDLL('kernel32',use_last_error=True)
        self.a=C.WinDLL('advapi32',use_last_error=True)
        self.u=C.WinDLL('userenv',use_last_error=True)
        self.ole=C.WinDLL('ole32',use_last_error=True)
        self.k.GetCurrentProcess.restype=W.HANDLE
        self.k.GetCurrentPackageFamilyName.argtypes=[C.POINTER(W.DWORD),W.LPWSTR]
        self.k.GetCurrentPackageFamilyName.restype=C.c_long
        self.k.CloseHandle.argtypes=[W.HANDLE]
        self.k.LocalFree.argtypes=[C.c_void_p];self.k.LocalFree.restype=C.c_void_p
        self.a.FreeSid.argtypes=[C.c_void_p];self.a.FreeSid.restype=C.c_void_p
        self.ole.CoTaskMemFree.argtypes=[C.c_void_p]
        self.a.OpenProcessToken.argtypes=[W.HANDLE,W.DWORD,C.POINTER(W.HANDLE)];self.a.OpenProcessToken.restype=W.BOOL
        self.a.GetTokenInformation.argtypes=[W.HANDLE,C.c_int,C.c_void_p,W.DWORD,C.POINTER(W.DWORD)];self.a.GetTokenInformation.restype=W.BOOL
        self.a.ConvertSidToStringSidW.argtypes=[C.c_void_p,C.POINTER(W.LPWSTR)];self.a.ConvertSidToStringSidW.restype=W.BOOL
        self.a.ConvertStringSidToSidW.argtypes=[W.LPCWSTR,C.POINTER(C.c_void_p)];self.a.ConvertStringSidToSidW.restype=W.BOOL
        self.a.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes=[W.LPCWSTR,W.DWORD,C.POINTER(C.c_void_p),C.c_void_p];self.a.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype=W.BOOL
        self.a.GetSecurityDescriptorDacl.argtypes=[C.c_void_p,C.POINTER(W.BOOL),C.POINTER(C.c_void_p),C.POINTER(W.BOOL)];self.a.GetSecurityDescriptorDacl.restype=W.BOOL
        self.a.SetNamedSecurityInfoW.argtypes=[W.LPWSTR,W.DWORD,W.DWORD,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p];self.a.SetNamedSecurityInfoW.restype=W.DWORD
        self.u.CreateAppContainerProfile.argtypes=[W.LPCWSTR,W.LPCWSTR,W.LPCWSTR,C.c_void_p,W.DWORD,C.POINTER(C.c_void_p)];self.u.CreateAppContainerProfile.restype=C.c_long
        self.u.GetAppContainerFolderPath.argtypes=[W.LPCWSTR,C.POINTER(W.LPWSTR)];self.u.GetAppContainerFolderPath.restype=C.c_long
        self.u.DeleteAppContainerProfile.argtypes=[W.LPCWSTR];self.u.DeleteAppContainerProfile.restype=C.c_long
        token=W.HANDLE();self._check(self.a.OpenProcessToken(self.k.GetCurrentProcess(),8,C.byref(token)))
        try:
            for kind in (20,29):
                flag=W.DWORD();size=W.DWORD()
                self._check(self.a.GetTokenInformation(token,kind,C.byref(flag),4,C.byref(size)))
                if flag.value:raise RuntimeError('use an ordinary non-elevated, non-AppContainer broker')
            size=W.DWORD();self.a.GetTokenInformation(token,1,None,0,C.byref(size))
            buffer=C.create_string_buffer(size.value)
            self._check(self.a.GetTokenInformation(token,1,buffer,size,C.byref(size)))
            self.user_sid=self._sid_text(C.c_void_p.from_buffer(buffer).value)
        finally:self.k.CloseHandle(token)
        count=W.DWORD();status=self.k.GetCurrentPackageFamilyName(C.byref(count),None)
        if status!=15700:  # APPMODEL_ERROR_NO_PACKAGE
            if status!=122 or not 0<count.value<=1024:raise OSError('cannot query current package identity: '+str(status))
            raise RuntimeError('AppContainer qualification requires an unpackaged Python broker; '
                               'Microsoft Store Python is not supported. Select an ordinary '
                               'python.org Python executable. No profile was created.')

    @staticmethod
    def _check(value):
        if not value:raise C.WinError(C.get_last_error())
        return value

    def _sid_text(self,sid):
        text=self.W.LPWSTR();self._check(self.a.ConvertSidToStringSidW(sid,C.byref(text)))
        try:return text.value
        finally:self.k.LocalFree(text)

    def create(self):
        self._owner()
        if self.created or self.deleted:raise RuntimeError('profile object is single-use')
        pointer=C.c_void_p()
        class SIDATTR(C.Structure):_fields_=[('sid',C.c_void_p),('attributes',self.W.DWORD)]
        buffers=[]
        try:
            canonical=[]
            for sid in self.capabilities:
                value=C.c_void_p();self._check(self.a.ConvertStringSidToSidW(sid,C.byref(value)));buffers.append(value)
                name=self._sid_text(value)
                if name in canonical:raise ValueError('duplicate capability')
                canonical.append(name)
            self.capabilities=canonical
            items=(SIDATTR*len(buffers))(*(SIDATTR(p,4)for p in buffers))
            hr=self.u.CreateAppContainerProfile(self.name,'NEX SDK qualification',
                'Owned temporary standard-user SDK test profile',items if buffers else None,
                len(buffers),C.byref(pointer))
        finally:
            for value in buffers:self.k.LocalFree(value)
        if hr!=0:raise OSError('CreateAppContainerProfile failed; existing profile not reused: '+str(hr))
        self.created=True
        try:
            self.sid=self._sid_text(pointer);text=self.W.LPWSTR()
            hr=self.u.GetAppContainerFolderPath(self.sid,C.byref(text))
            if hr!=0:raise OSError('GetAppContainerFolderPath failed: '+str(hr))
            try:self.path=Path(text.value).resolve(strict=True)
            finally:self.ole.CoTaskMemFree(text)
            if (self.path.name.casefold()!='ac' or
                    self.path.parent.name.casefold()!=self.name.casefold()):
                raise RuntimeError('new AppContainer profile path does not match its moniker')
            self._acl(self.path,'0x1200a9')
            self.work=self.path/'work';self.work.mkdir();self._acl(self.work,'0x1301bf')
            return self
        except BaseException:
            self.close();raise
        finally:self.a.FreeSid(pointer)

    def _acl(self,path,rights):
        path=Path(path)
        if path.lstat().st_file_attributes&0x400:raise ValueError('profile ACL target is a reparse point')
        path=path.resolve(strict=True)
        if self.path is None or (path!=self.path and self.path not in path.parents):
            raise ValueError('ACL changes are restricted to this freshly-created profile')
        if path.lstat().st_file_attributes&0x400:raise ValueError('profile ACL target is a reparse point')
        descriptor=C.c_void_p()
        sddl=('D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FA;;;'+self.user_sid+
              ')(A;OICI;'+rights+';;;'+self.sid+')')
        self._check(self.a.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl,1,C.byref(descriptor),None))
        try:
            present=self.W.BOOL();defaulted=self.W.BOOL();acl=C.c_void_p()
            self._check(self.a.GetSecurityDescriptorDacl(descriptor,C.byref(present),C.byref(acl),C.byref(defaulted)))
            if not present.value:raise RuntimeError('new profile DACL is absent')
            error=self.a.SetNamedSecurityInfoW(str(path),1,4|0x80000000,None,None,acl,None)
            if error:raise C.WinError(error)
        finally:self.k.LocalFree(descriptor)

    def copy_tree(self,source,name='sdk',*,max_files=100000,max_bytes=8*1024**3):
        self._owner()
        if not self.created or self.deleted:raise RuntimeError('create the profile first')
        if not self.safe_to_cleanup:raise RuntimeError('a profile operation is still active')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}',name)or name.endswith('.'):
            raise ValueError('SDK copy name must be a single safe path component')
        source=Path(source).absolute()
        if not source.is_dir():raise ValueError('SDK source must be a directory')
        files=[];directories=[];pending=[source];entries=0
        while pending:
            directory=pending.pop()
            if directory.is_symlink()or directory.lstat().st_file_attributes&0x400:
                raise ValueError('SDK source contains a link/reparse point')
            for path in directory.iterdir():
                entries+=1
                if entries>max_files*2:raise ValueError('SDK tree has too many entries')
                if path.is_symlink()or path.lstat().st_file_attributes&0x400:
                    raise ValueError('SDK source contains a link/reparse point')
                if path.is_dir():directories.append(path.relative_to(source));pending.append(path)
                elif path.is_file():files.append(path)
                else:raise ValueError('SDK source contains a non-file entry')
        total=sum(p.stat().st_size for p in files)
        if len(files)>max_files or total>max_bytes:raise ValueError('SDK copy exceeds its explicit bounds')
        if shutil.disk_usage(self.path).free<total+100*1024**2:raise RuntimeError('not enough space for the SDK copy')
        target=self.path/name
        if target.exists():raise ValueError('SDK copy destination must be new')
        target.mkdir();inventory={}
        for directory in sorted(directories,key=lambda p:len(p.parts)):
            (target/directory).mkdir(parents=True,exist_ok=True)
        for path in files:
            relative=path.relative_to(source);output=target/relative
            output.parent.mkdir(parents=True,exist_ok=True)
            before=sha(path)
            with path.open('rb')as original,output.open('xb')as copied:shutil.copyfileobj(original,copied,1024*1024)
            if sha(output)!=before or sha(path)!=before:raise RuntimeError('SDK source changed during copy: '+str(path))
            output.chmod(path.stat().st_mode&0o777)
            inventory[relative.as_posix()]={'sha256':before,'bytes':output.stat().st_size}
        self._acl(target,'0x1200a9')
        self.copies.append({'source':str(source),'directory':str(target),'files':inventory,
                            'directories':[p.as_posix()for p in directories],'bytes':total})
        return target

    def run(self,command,output,environment,*,observer,timeout=180):
        self._owner()
        if not self.created or self.deleted:raise RuntimeError('profile is not active')
        if not self.safe_to_cleanup:raise RuntimeError('a profile operation is still active')
        if not command or not Path(command[0]).is_absolute():raise ValueError('absolute command required')
        if not 0<timeout<=10800:raise ValueError('job timeout must be in (0, 10800] seconds')
        observer=Path(observer).resolve(strict=True)
        described=subprocess.run([str(observer),'--describe'],capture_output=True,text=True,timeout=10)
        if described.returncode!=0:raise RuntimeError('selected observer does not support AppContainer creation')
        features=json.loads(described.stdout)
        if (features.get('schema')!='nex.windows-job-observer-capabilities/1' or
                features.get('appcontainer_at_creation')is not True or
                features.get('kernel_job_assignment_at_creation')is not True or
                features.get('root_token_verified_before_resume')is not True or
                features.get('explicit_working_directory')is not True):
            raise RuntimeError('selected observer lacks the required verified AppContainer contract')
        if timeout>3600:
            maximum=features.get('maximum_timeout_ms')
            if type(maximum)is not int or maximum<int(timeout*1000):
                raise ValueError('selected observer does not advertise the requested workflow budget')
        output=Path(output).resolve()
        if output.exists():raise ValueError('observation output must be new')
        if output==self.path or self.path in output.parents:
            raise ValueError('observation evidence must survive outside the profile')
        self.safe_to_cleanup=False
        try:
            value=observe(command,output,environment,observer=observer,timeout=timeout,
                directory=self.work,appcontainer_sid=self.sid,capabilities=self.capabilities)
            self.safe_to_cleanup=value['active_job_processes']==0
            self.runs.append(value);return value
        except BaseException:
            # A failed command may still have a conclusive private-job receipt.
            receipt=output/'owned.json'
            if receipt.is_file():
                data=json.loads(receipt.read_text(encoding='utf-8'))
                never_created=(data.get('created_root')is False and data.get('root_pid')==0 and
                               data.get('root_resumed')is False)
                retired=(data.get('final_job_accounting_observed')is True and
                         data.get('active_job_processes')==0 and
                         all(p.get('exited')is True for p in data.get('processes',[])))
                self.safe_to_cleanup=never_created or retired
            raise

    def _owner(self):
        if threading.get_ident()!=self.owner_thread:
            raise RuntimeError('each profile is controlled by its creating broker thread')

    def verify_copies(self):
        self._owner()
        if not self.safe_to_cleanup:raise RuntimeError('job retirement must be proven first')
        for copy in self.copies:
            for directory in ('source','directory'):
                root=Path(copy[directory]);files=set();directories=set()
                for path in root.rglob('*'):
                    if path.is_symlink()or path.lstat().st_file_attributes&0x400:
                        raise RuntimeError('SDK tree acquired a link/reparse point: '+str(path))
                    name=path.relative_to(root).as_posix()
                    if path.is_dir():directories.add(name)
                    elif path.is_file():files.add(name)
                    else:raise RuntimeError('SDK tree acquired a non-file entry: '+str(path))
                if files!=set(copy['files'])or directories!=set(copy['directories']):
                    raise RuntimeError('SDK tree entries changed: '+str(root))
            for name,row in copy['files'].items():
                for directory in ('source','directory'):
                    path=Path(copy[directory])/name
                    if path.stat().st_size!=row['bytes']or sha(path)!=row['sha256']:
                        raise RuntimeError('SDK bytes changed: '+str(path))

    def close(self):
        self._owner()
        if not self.created or self.deleted:return
        if not self.safe_to_cleanup:
            raise RuntimeError('profile retained: physical job retirement not proven; '+self.name)
        for attempt in range(3):
            hr=self.u.DeleteAppContainerProfile(self.name)
            if hr==0 and self.path is not None and not self.path.exists():
                self.deleted=True;return
            time.sleep(.1)
        raise RuntimeError('temporary profile deletion not verified: '+self.name+'; HRESULT '+str(hr))

    def __enter__(self):return self.create()
    def __exit__(self,kind,value,traceback):self.close()
