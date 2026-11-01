"""Build/run/test and snapshot/recover a real project with local Windows NEX."""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import winreg

ROOT=Path(__file__).resolve().parents[2]


def context():
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    security=ctypes.WinDLL('advapi32',use_last_error=True)
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    security.OpenProcessToken.argtypes=[wintypes.HANDLE,wintypes.DWORD,ctypes.POINTER(wintypes.HANDLE)]
    security.GetTokenInformation.argtypes=[wintypes.HANDLE,ctypes.c_int,wintypes.LPVOID,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]
    token=wintypes.HANDLE()
    if not security.OpenProcessToken(kernel.GetCurrentProcess(),8,ctypes.byref(token)):raise ctypes.WinError(ctypes.get_last_error())
    try:
        result={}
        for name,kind in [('is_elevated',20),('is_app_container',29)]:
            value=wintypes.DWORD();count=wintypes.DWORD()
            if not security.GetTokenInformation(token,kind,ctypes.byref(value),ctypes.sizeof(value),ctypes.byref(count)):raise ctypes.WinError(ctypes.get_last_error())
            result[name]=bool(value.value)
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock') as key:
                result['developer_mode']=winreg.QueryValueEx(key,'AllowDevelopmentWithoutDevLicense')[0]==1
        except FileNotFoundError:result['developer_mode']=False
        return result
    finally:kernel.CloseHandle(token)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    assert os.name=='nt'
    executable=args.compiler.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    token=context();assert not token['is_elevated'] and not token['is_app_container'],token
    (out/'context.json').write_text(json.dumps(token,indent=2)+'\n',encoding='utf-8')
    commands=[]
    def command(label,argv,cwd):
        result=subprocess.run(list(map(str,argv)),cwd=cwd,capture_output=True,timeout=180)
        (out/(label+'.stdout')).write_bytes(result.stdout);(out/(label+'.stderr')).write_bytes(result.stderr)
        commands.append({'argv':list(map(str,argv)),'cwd':str(cwd),'exit_code':result.returncode})
        assert result.returncode==0,(label,result.stdout,result.stderr)
        return result.stdout
    def cli(label,cwd,*argv):return json.loads(command(label,[executable,*argv,'--json'],cwd))
    project=out/'Проект 🧠';project.mkdir()
    for name in ('nex.json','main.nex'):shutil.copy2(ROOT/'examples/windows-host'/name,project/name)
    expected='NEX: локальная Windows 🧠\n42\n'
    run=cli('run',project,'run');assert run['stdout']==expected
    built=cli('build',project,'build','--profile','release')
    tests=cli('test',project,'test');assert tests['ok'] and tests['tests']
    application=out/'hello.exe';shutil.copy2(built['executable'],application)
    shutil.copy2(built['notices'],out/'runtime-notices.txt')
    assert application.read_bytes()[:2]==b'MZ'
    assert command('standalone',[application],out)==expected.encode('utf-8')
    snapshot=cli('snapshot',project,'snapshot','--directory',out/'snapshot')
    recovered=cli('recover',out,'recover',out/'snapshot','--directory',out/'recovered')
    assert snapshot['head']==recovered['head'] and snapshot['namespace']==recovered['namespace']
    assert hashlib.sha256((out/'recovered/.nex/graph.db').read_bytes()).hexdigest()==snapshot['database_sha256']
    # Recovery deliberately restores the graph without materializing sources.
    recovered_run=cli('recovered-run',out/'recovered','run','--revision','HEAD');assert recovered_run['stdout']==expected
    exported=cli('export',out/'recovered','export','--revision','HEAD','--directory',out/'exported')
    exported_run=cli('exported-run',out/'exported','run');assert exported_run['stdout']==expected
    value={'schema':'nex.windows-host-smoke/1','ok':True,'requires_WSL':False,
           'compiler_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),
           'application':str(application),'application_sha256':hashlib.sha256(application.read_bytes()).hexdigest(),
           'stdout':expected,'test':tests,'snapshot':snapshot,'recovery':recovered,'export':exported,'commands':commands,'context':token}
    (out/'report.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'ok':True,'report':str(out/'report.json'),'application':str(application)}))


if __name__=='__main__':main()
