"""Native code staging, read isolation and owned-root lifetime regressions."""
from pathlib import Path
import argparse,ctypes as C,hashlib,json,os,shutil,stat,sys,tempfile,time,traceback
from ctypes import wintypes as W
from appcontainer import Profile,sha

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--observer',required=True,type=Path)
parser.add_argument('--probe',required=True,type=Path)
parser.add_argument('--runtime',required=True,type=Path)
parser.add_argument('--code-parent',required=True,type=Path)
parser.add_argument('--output',type=Path)
args=parser.parse_args()
if os.name!='nt':parser.error('native Windows is required')
root=args.output.resolve()if args.output else Path(tempfile.mkdtemp(prefix='nex-code-root-test-'))
if args.output:root.mkdir(parents=True,exist_ok=False)
started=time.monotonic();p=None;other=None;roots=[];saved={};canary_root=None
r={'schema':'nex.windows-private-code-root-regression/1','ok':False,'state':'starting','output':str(root),'cases':[],'original_or_existing_ACLs_changed':False,'global_mitigations_changed':False,'whole_SDK_accepted':False}
def save():
 r['seconds']=time.monotonic()-started;(root/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
def check(name):r['cases'].append({'name':name,'ok':True});save()
try:
 helper=args.observer.resolve(strict=True);probe=args.probe.resolve(strict=True);runtime=args.runtime.resolve(strict=True)
 r['probe_sha256']=sha(probe);p=Profile();p.create();other=Profile();other.create()
 p.a.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes=[C.c_void_p,W.DWORD,W.DWORD,C.POINTER(W.LPWSTR),C.c_void_p];p.a.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype=W.BOOL
 def fingerprint(path):
  h=p._cleanup_open(path)
  try:
   identity,attrs=p._cleanup_metadata(h);desc=C.c_void_p();err=p.a.GetSecurityInfo(h,1,7,None,None,None,None,C.byref(desc));assert err==0,err
   try:
    text=W.LPWSTR();p._check(p.a.ConvertSecurityDescriptorToStringSecurityDescriptorW(desc,1,7,C.byref(text),None))
    try:sddl=text.value
    finally:p.k.LocalFree(text)
   finally:p.k.LocalFree(desc)
  finally:p.k.CloseHandle(h)
  return {'identity':[identity[0],identity[1].hex()],'attrs':attrs,'SDDL':sddl,'sha256':sha(path)if path.is_file()else None}
 parent_before=fingerprint(args.code_parent.resolve(strict=True));inputs=root/'inputs';inputs.mkdir();shutil.copyfile(probe,inputs/'path.exe')
 code=p.code_root(args.code_parent);code.create();roots.append(code);image=code.copy_tree(inputs,max_files=2,max_bytes=16*1024**2)/'path.exe'
 opposite=other.copy_tree(inputs,'opposite',max_files=2,max_bytes=16*1024**2)/'path.exe';python=code.copy_tree(runtime,'python',max_files=1000,max_bytes=64*1024**2)/'python.exe'
 env={k:v for k,v in os.environ.items()if not k.startswith(('NEX_','PYTHON'))};env.update(PATH='C:/Windows/System32;C:/Windows',PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1');env=p.native_environment(env)
 def run(label,argv):
  r['state']=label;save();out=root/label;v=p.run(list(map(str,argv)),out,env,observer=helper,timeout=30);r.setdefault('observations',[]).append(dict(v,label=label));save();assert v['parent_exit_code']==0 and not v['timed_out']and v['active_job_processes']==0,(label,(out/'stderr').read_text(errors='replace'));return(out/'stdout').read_text(encoding='utf-8')
 text=run('long-path',[image,image]);assert 'OWN_LONG_PATH_LENGTH 0 'not in text and 'TARGET_LONG_PATH_LENGTH 0 'not in text;check('full-executable-long-name-resolves-inside-AppContainer')
 peer=p.work/'peer.py';peer.write_text('''from pathlib import Path
import json,sys
image=Path(sys.argv[1]);assert image.read_bytes()[:2]==b'MZ'
try:
 with image.open('r+b'):pass
except PermissionError:pass
else:raise AssertionError('code copy writable')
for name in sys.argv[2:]:
 try:
  with Path(name).open('rb')as f:f.read(1)
 except PermissionError:pass
 else:raise AssertionError('outside read permitted')
q=Path('own-work');q.write_text('42');assert q.read_text()=='42';q.unlink();print(json.dumps({'ok':True}))
''',encoding='utf-8');assert json.loads(run('read-write-boundaries',[python,'-I','-B',peer,image,probe,opposite]))['ok'];check('code-readonly-original-and-opposite-denied-work-writable')
 p.safe_to_cleanup=False
 try:
  try:code.close()
  except RuntimeError as error:assert 'job retirement'in str(error)
  else:raise AssertionError('unretired-profile flag admitted cleanup')
 finally:p.safe_to_cleanup=True
 code.verify_copies();assert image.exists();check('unretired-profile-guard-retains-code')
 canary_root=tempfile.TemporaryDirectory(prefix='nex-code-canary-',dir=args.code_parent);outside=Path(canary_root.name);canary=outside/'keep';canary.write_bytes(b'keep\x00');canary.chmod(stat.S_IREAD);before=fingerprint(canary);before_dir=fingerprint(outside)
 guards=p.code_root(args.code_parent);guards.create();roots.append(guards);assert guards.path.drive.casefold()==canary.drive.casefold();os.symlink(str(outside),guards.path/'external-directory',target_is_directory=True);os.link(canary,guards.path/'external-hardlink');guards.close();assert not guards.path.exists();assert fingerprint(canary)==before and fingerprint(outside)==before_dir;check('code-cleanup-unlinks-reparse-and-hardlink-without-outside-change')
 guards=p.code_root(args.code_parent);guards.create();roots.append(guards);held=guards.path.with_name(guards.path.name+'-held');guards.path.rename(held);saved[guards]=held;guards.path.mkdir();sentinel=guards.path/'keep';sentinel.write_bytes(b'replacement');replacement=fingerprint(guards.path)
 try:guards.close()
 except RuntimeError as error:assert 'root identity changed'in str(error)
 else:raise AssertionError('replaced code root admitted')
 assert fingerprint(guards.path)==replacement and sentinel.read_bytes()==b'replacement';sentinel.unlink();guards.path.rmdir();held.rename(guards.path);saved.pop(guards);guards.close();check('replaced-code-root-retained-without-modification')
 bounded=p.code_root(args.code_parent,max_cleanup_entries=2);bounded.create();roots.append(bounded);(bounded.path/'a').mkdir();(bounded.path/'a/b').write_bytes(b'owned')
 try:bounded.close()
 except RuntimeError as error:assert 'entry bound'in str(error)
 else:raise AssertionError('code cleanup entry bound ignored')
 assert bounded.path.exists()and not bounded.deleted;bounded.max_cleanup_entries=200000;bounded.close();check('code-entry-bound-retains-then-explicit-retry-cleans')
 assert code.created and not code.deleted;p.close();assert code.deleted and not code.path.exists();assert all(c.deleted for c in roots);check('profile-close-also-deletes-tracked-code-roots')
 assert fingerprint(args.code_parent.resolve(strict=True))==parent_before;assert sha(probe)==r['probe_sha256'];r.update(ok=True,state='private-code-lifetime-access-and-long-name-controls-passed')
except BaseException as error:r.update(state='failed',error=repr(error),traceback=traceback.format_exc());save()
finally:
 for code,held in list(saved.items()):
  try:
   sentinel=code.path/'keep'
   if sentinel.is_file()and not sentinel.is_symlink()and sentinel.read_bytes()==b'replacement':sentinel.unlink()
   code.path.rmdir();held.rename(code.path);saved.pop(code)
  except BaseException as error:r.setdefault('cleanup_errors',[]).append(repr(error))
 for code in roots:
  if code.created and not code.deleted:
   try:
    if code.max_cleanup_entries==2:code.max_cleanup_entries=200000
    code.close()
   except BaseException as error:r.setdefault('cleanup_errors',[]).append(repr(error))
 for profile in [other,p]:
  if profile is not None and profile.created:
   try:profile.close()
   except BaseException as error:r.setdefault('cleanup_errors',[]).append(repr(error))
 if canary_root is not None:
  try:
   path=Path(canary_root.name)/'keep'
   if path.exists():path.chmod(stat.S_IREAD|stat.S_IWRITE)
   canary_root.cleanup()
  except BaseException as error:r.setdefault('cleanup_errors',[]).append(repr(error))
 r['code_roots_absent']=all(c.deleted and not c.path.exists()for c in roots);r['profiles_absent']=all(profile is None or(not profile.path.exists()and not profile.path.parent.exists())for profile in [p,other])
 if r.get('cleanup_errors')or not r['code_roots_absent']or not r['profiles_absent']:r.update(ok=False,state='failed-cleanup')
 save()
print(json.dumps({k:r.get(k)for k in ['ok','state','error','output','code_roots_absent','profiles_absent','cleanup_errors']}));raise SystemExit(0 if r['ok']else 1)
