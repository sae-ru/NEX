"""Native AppContainer/private-job calibration using only controlled peers."""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

from appcontainer import Profile, sha

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--observer',required=True,type=Path)
parser.add_argument('--runtime',type=Path,help='Compact ordinary Windows Python runtime to copy (at most64MiB)')
parser.add_argument('--output',type=Path,help='New retained evidence directory; successful temporary evidence is otherwise removed')
parser.add_argument('--source-canary',type=Path,help='Existing readable file to test denial; observed only, never modified')
parser.add_argument('--expect-packaged-broker-refusal',action='store_true',
                    help='Verify refusal of a real packaged broker before creating any profile')
args=parser.parse_args()
if os.name!='nt':parser.error('native Windows is required')
root=args.output.resolve()if args.output else Path(tempfile.mkdtemp(prefix='NEX app containers, % 🧠 '))
if args.output:root.mkdir(parents=True,exist_ok=False)
started=time.monotonic();profiles=[];outside=None
report={'schema':'nex.windows-AppContainer-job-calibration/1','ok':False,'state':'preflight',
        'controller_python':sys.version,'controller_pid':os.getpid(),'cases':[],
        'network_policy_changed':False,'original_source_ACLs_changed':False,
        'whole_SDK_accepted':False}
def save():
    report['seconds']=time.monotonic()-started
    p=root/'report.tmp';p.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');p.replace(root/'report.json')
peer_source=r'''from pathlib import Path
import ctypes as C
from ctypes import wintypes as W
import json,os,subprocess,sys,time
mode=sys.argv[1];canaries=json.loads(sys.argv[2]);sdk=Path(sys.executable).parent
k=C.WinDLL('kernel32',use_last_error=True);a=C.WinDLL('advapi32',use_last_error=True)
k.GetCurrentProcess.restype=W.HANDLE;k.CloseHandle.argtypes=[W.HANDLE]
k.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE];k.CreateFileW.restype=W.HANDLE
a.OpenProcessToken.argtypes=[W.HANDLE,W.DWORD,C.POINTER(W.HANDLE)];a.GetTokenInformation.argtypes=[W.HANDLE,C.c_int,C.c_void_p,W.DWORD,C.POINTER(W.DWORD)]
t=W.HANDLE();assert a.OpenProcessToken(k.GetCurrentProcess(),8,C.byref(t))
try:
 flag=W.DWORD();size=W.DWORD();assert a.GetTokenInformation(t,29,C.byref(flag),4,C.byref(size));assert flag.value==1
finally:k.CloseHandle(t)
def denied(path,rights,disposition=3):
 h=k.CreateFileW(str(path),rights,3,None,disposition,0x80,None)
 if h!=C.c_void_p(-1).value:k.CloseHandle(h);raise AssertionError(('unexpected access',path,rights))
 assert C.get_last_error()==5,(path,rights,C.get_last_error())
for path in canaries:denied(path,0x80000000)
result={'pid':os.getpid(),'AppContainer':True,'strict_executable':str(Path(sys.executable).resolve(strict=True)),'denied_canaries':canaries}
if mode=='sleeper':
 Path('orphan-child.json').write_text(json.dumps(result));time.sleep(60);sys.exit(9)
if mode=='grandchild':print(json.dumps(result));sys.exit(0)
for rights in [0x40000000,0x40000,0x10000]:denied(sys.executable,rights)
denied(sdk/'must-not-create.txt',0x40000000,4)
Path('work-output.txt').write_text('owned work')
if mode=='nonzero':print(json.dumps(result));sys.exit(7)
if mode=='orphan':
 child=subprocess.Popen([sys.executable,'-I','-B',__file__,'sleeper',sys.argv[2]])
 until=time.monotonic()+5
 while not Path('orphan-child.json').exists():assert time.monotonic()<until;time.sleep(.01)
 print(json.dumps(result));sys.exit(0)
child=subprocess.run([sys.executable,'-I','-B',__file__,'grandchild',sys.argv[2]],capture_output=True,text=True,timeout=15)
assert child.returncode==0,(child.returncode,child.stdout,child.stderr)
result['grandchild']=json.loads(child.stdout);result['ok']=True
print(json.dumps(result))
'''
compile(peer_source,'AppContainer peer','exec')
try:
    if args.expect_packaged_broker_refusal:
        try:Profile()
        except RuntimeError as error:
            assert 'requires an unpackaged Python broker' in str(error),str(error)
            report.update(ok=True,state='passed',packaged_broker_refused_before_create=True)
            report['cases'].append({'name':'packaged-broker-refused-before-create','ok':True})
            save()
            print(json.dumps(report))
            if not args.output:shutil.rmtree(root)
            raise SystemExit(0)
        raise AssertionError('packaged broker was not refused')
    if args.runtime is None:raise ValueError('--runtime is required for AppContainer execution')
    runtime=args.runtime.resolve(strict=True);assert (runtime/'python.exe').is_file()
    observer=args.observer.resolve(strict=True)
    outside_file=root/'outside-file.txt';outside_file.write_text('ordinary broker readable')
    source_canary=args.source_canary.resolve(strict=True)if args.source_canary else outside_file
    report['source_canary_sha256']=sha(source_canary)
    stop=root/'outside-stop'
    outside=subprocess.Popen([str(runtime/'python.exe'),'-I','-B','-c',
        'from pathlib import Path;import sys,time;stop=Path(sys.argv[1]);end=time.monotonic()+120\nwhile not stop.exists():\n if time.monotonic()>end:sys.exit(19)\n time.sleep(.02)\n',str(stop)],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    assert outside.poll()is None
    report['outside_canary_pid']=outside.pid;save()
    # A separate profile is never implicitly readable by the active profile.
    other=Profile();profiles.append(other);other.create()
    fixture=root/'opposite-source';fixture.mkdir();(fixture/'canary.txt').write_text('opposite SDK')
    (fixture/'empty-directory').mkdir();opposite=other.copy_tree(fixture)
    assert (opposite/'empty-directory').is_dir()
    profile=Profile();profiles.append(profile);profile.create()
    try:
        collision=Profile(name=profile.name)
        try:collision.create()
        except OSError:pass
        else:raise AssertionError('an existing profile was reused')
        assert profile.path.exists()and not collision.created
        report['cases'].append({'name':'existing-profile-not-reused','ok':True})
        try:profile._acl(outside_file,'FA')
        except ValueError:pass
        else:raise AssertionError('an original file ACL was mutable through the profile API')
        report['cases'].append({'name':'ACL-target-outside-owned-profile-rejected','ok':True})
        sdk=profile.copy_tree(runtime,'python',max_files=1000,max_bytes=64*1024**2)
        peer=profile.work/'peer.py';peer.write_text(peer_source,encoding='utf-8')
        environment={**os.environ,'TEMP':str(profile.work),'TMP':str(profile.work),
                     'LOCALAPPDATA':str(profile.work),'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1'}
        canaries=json.dumps([str(outside_file),str(source_canary),str(opposite/'canary.txt')])
        for label,expected,budget in [('healthy',0,20),('nonzero',7,20),('orphan',0,1.5)]:
            report['state']=label;save()
            observed=profile.run([str(sdk/'python.exe'),'-I','-B',str(peer),label,canaries],
                root/label,environment,observer=observer,timeout=budget)
            assert observed['parent_exit_code']==expected and observed['timed_out']==(label=='orphan')
            assert observed['appcontainer_verified_before_resume']and observed['appcontainer_sid']==profile.sid
            assert observed['active_job_processes']==0 and outside.poll()is None
            profile.verify_copies();other.verify_copies()
            if label=='healthy':
                value=json.loads((root/label/'stdout').read_text(encoding='utf-8'))
                assert value['ok']and value['grandchild']['AppContainer']
            if label=='orphan':
                child=json.loads((profile.work/'orphan-child.json').read_text(encoding='utf-8'))
                assert child['AppContainer']
                captured=next(p for p in observed['children']if p['pid']==child['pid'])
                assert captured['exited']and captured['exit_code']==238
            report['cases'].append({'name':label,'ok':True,'observation':observed});save()
    finally:
        profile.close();other.close()
    # A declared capability must be present in the suspended root token too.
    cap=Profile(capabilities=['S-1-15-3-1']);profiles.append(cap);cap.create()
    try:
        sdk=cap.copy_tree(runtime,'python',max_files=1000,max_bytes=64*1024**2)
        peer=cap.work/'peer.py';peer.write_text(peer_source,encoding='utf-8')
        observed=cap.run([str(sdk/'python.exe'),'-I','-B',str(peer),'healthy',json.dumps([str(source_canary)])],
            root/'explicit-capability',{**os.environ,'TEMP':str(cap.work),'TMP':str(cap.work),
                'LOCALAPPDATA':str(cap.work),'PYTHONDONTWRITEBYTECODE':'1'},observer=observer,timeout=20)
        assert observed['parent_exit_code']==0 and observed['appcontainer_capabilities']==['S-1-15-3-1']
        assert not observed['timed_out']and outside.poll()is None
        cap.verify_copies();report['cases'].append({'name':'explicit-capability-token-verified','ok':True,'observation':observed})
    finally:cap.close()
    for invalid in ('S-1-5-32-544','S-1-15-2-1'):
        try:Profile(capabilities=[invalid])
        except ValueError:pass
        else:raise AssertionError('non-capability SID accepted')
    assert sha(source_canary)==report['source_canary_sha256']
    stop.write_text('stop');assert outside.wait(timeout=5)==0
    assert all(p.deleted and not p.path.exists()for p in profiles)
    report.update(ok=True,state='passed',profiles_deleted=True,
        outside_canary_cooperative_exit=0,source_canary_content_unchanged=True,
        copies=[copy for p in profiles for copy in p.copies],
        profiles=[{'name':p.name,'SID':p.sid,'path':str(p.path),'deleted':p.deleted}for p in profiles])
except SystemExit:
    raise
except BaseException as error:
    report.update(state='failed',error=repr(error),traceback=traceback.format_exc())
finally:
    for profile in reversed(profiles):
        if profile.created and not profile.deleted:
            try:profile.close()
            except BaseException as error:report.setdefault('cleanup_errors',[]).append({'profile':profile.name,'error':repr(error)})
    if outside is not None and outside.poll()is None:
        (root/'outside-stop').write_text('stop')
        try:outside.wait(timeout=5)
        except subprocess.TimeoutExpired:outside.terminate();outside.wait(timeout=5)
    if not args.expect_packaged_broker_refusal or not report['ok']:
        report['profiles']=[{'name':p.name,'SID':p.sid,'path':str(p.path)if p.path else None,
                            'created':p.created,'deleted':p.deleted,
                            'path_absent':p.path is not None and not p.path.exists()}for p in profiles]
        report['profiles_deleted']=all(not p.created or(p.deleted and not p.path.exists())for p in profiles)
        report['outside_canary_cooperative_exit']=outside.returncode if outside is not None else None
        if 'source_canary_sha256'in report:
            report['source_canary_content_unchanged']=sha(source_canary)==report['source_canary_sha256']
        save()
print(json.dumps({k:report.get(k)for k in ['ok','state','error','seconds','cleanup_errors']}))
if report['ok']and not args.output:shutil.rmtree(root)
raise SystemExit(0 if report['ok']else 1)
